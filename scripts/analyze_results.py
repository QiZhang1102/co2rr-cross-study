#!/usr/bin/env python3
"""Recompute every reported metric/figure from saved outer predictions."""
import argparse, json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

KEYS=['split','model','feature_set','calibration']

def confusion(y, pred, k, weights=None):
    return np.bincount(y*k+pred,weights=weights,minlength=k*k).reshape(k,k)

def cm_metrics(cm):
    tp=np.diag(cm); support=cm.sum(1); predicted=cm.sum(0)
    recall=np.divide(tp,support,out=np.zeros_like(tp,dtype=float),where=support>0)
    precision=np.divide(tp,predicted,out=np.zeros_like(tp,dtype=float),where=predicted>0)
    f1=np.divide(2*tp,support+predicted,out=np.zeros_like(tp,dtype=float),where=(support+predicted)>0)
    return float(f1.mean()),float(tp.sum()/cm.sum()),precision,recall,f1

def scores(y,p,study,k):
    pred=p.argmax(1); cm=confusion(y,pred,k)
    counts=pd.Series(study).value_counts()
    w=np.array([1/counts[s] for s in study]); weighted=confusion(y,pred,k,w)
    f,a,*_=cm_metrics(cm); ef,ea,*_=cm_metrics(weighted)
    one=np.eye(k)[y]
    ll=-np.log(np.maximum(p[np.arange(len(y)),y],1e-15))
    bs=((p-one)**2).sum(1)
    return {'n_records':len(y),'n_studies':len(counts),'macro_f1':f,'accuracy':a,'equal_study_macro_f1':ef,'equal_study_accuracy':ea,'log_loss':ll.mean(),'brier':bs.mean(),'equal_study_log_loss':np.average(ll,weights=w),'equal_study_brier':np.average(bs,weights=w)},cm,ll,bs

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--results',default='results');ap.add_argument('--figures',default='figures');ap.add_argument('--bootstrap',type=int,default=500);a=ap.parse_args()
    root=Path(__file__).resolve().parents[1];r=root/a.results;f=root/a.figures;f.mkdir(parents=True,exist_ok=True)
    cfg=json.loads((root/'configs/config.json').read_text());classes=cfg['classes'];k=len(classes)
    d=pd.read_csv(r/'predictions.csv'); records=pd.read_csv(root/'data/processed/records.csv'); pm=['p_'+x for x in classes]
    lookup={x:i for i,x in enumerate(classes)}
    features=cfg['feature_sets']['combined']
    records['missing_pattern']=records[features].isna().apply(lambda row: ','.join(row.index[row]) or 'none',axis=1)
    records['catalyst_family']=np.where(records.atom_N.gt(0),'N-containing modifier',np.where(records.atom_O.gt(0),'O-containing, no N modifier','other modifier'))
    assert list(x for x in d if x.startswith('p_'))==pm
    metrics=[];perclass=[];bins=[];risk=[];subgroups=[];studies=[];influence=[];cache={}
    for key,g in d.groupby(KEYS,sort=True):
        g=g.sort_values('record_id').reset_index(drop=True);meta=dict(zip(KEYS,key));
        assert g.record_id.is_unique
        if key[3]=='uncalibrated':assert set(g.record_id)==set(records.record_id), 'Incomplete main OOF sample'
        meta['complete_oof']=set(g.record_id)==set(records.record_id)
        p=g[pm].to_numpy(); y=g.y_true.map(lookup).to_numpy();s=g.study_id.to_numpy()
        assert np.isfinite(p).all() and (p>=0).all() and np.allclose(p.sum(1),1,atol=1e-8)
        assert np.array_equal(np.array(classes)[p.argmax(1)],g.y_pred)
        m,cm,ll,bs=scores(y,p,s,k)
        m['train_absent_true_class_n']=int((~g.train_has_true_class.astype(bool)).sum())
        _,_,pr,re,ff=cm_metrics(cm)
        for j,c in enumerate(classes):perclass.append(meta|{'class':c,'precision':pr[j],'recall':re[j],'f1':ff[j],'n_records':int((y==j).sum()),'n_studies':len(set(s[y==j]))})
        pd.DataFrame(cm,index=classes,columns=classes).to_csv(r/('confusion_'+'_'.join(key)+'.csv'))
        confidence=p.max(1);correct=(p.argmax(1)==y);b=np.minimum((confidence*10).astype(int),9)
        ece=0.0
        for j in range(10):
            ix=b==j
            if ix.any():ece+=ix.mean()*abs(confidence[ix].mean()-correct[ix].mean())
            if ix.any():bins.append(meta|{'bin':j,'lower':j/10,'upper':(j+1)/10,'n_records':int(ix.sum()),'n_studies':len(set(s[ix])),'confidence':confidence[ix].mean(),'accuracy':correct[ix].mean()})
        # Curves include all ties. No threshold is selected for deployment.
        for q in np.linspace(0,1,21):
            threshold=np.quantile(confidence,q);ix=confidence>=threshold
            risk.append(meta|{'threshold_exploratory':threshold,'coverage':ix.mean(),'accuracy':correct[ix].mean(),'risk':1-correct[ix].mean(),'n_records':int(ix.sum()),'n_studies':len(set(s[ix]))})
        for sid,ix0 in g.groupby('study_id').groups.items():
            ix=np.array(list(ix0));studies.append(meta|{'study_id':sid,'n_records':len(ix),'accuracy':correct[ix].mean(),'log_loss':ll[ix].mean(),'brier':bs[ix].mean()})
        ug=sorted(set(s)); groupcm=np.stack([confusion(y[s==sid],p[s==sid].argmax(1),k) for sid in ug])
        # Common source draw for every model/feature/calibration under each protocol.
        rng=np.random.default_rng(cfg['seed']+991);draws=rng.integers(0,len(ug),size=(a.bootstrap,len(ug)))
        estimates=np.array([cm_metrics(groupcm[draw].sum(0))[:2] for draw in draws])
        for j,name in enumerate(['macro_f1','accuracy']):m[name+'_ci_low'],m[name+'_ci_high']=np.quantile(estimates[:,j],[.025,.975])
        m['top_label_ece_10_bins']=ece
        metrics.append(meta|m)
        cache[key]=(g,y,p,ug,groupcm,draws,ll,bs)
        if key[0]=='study' and key[1]=='random_forest' and key[2]=='combined' and key[3]=='uncalibrated':
            for sid in ug:
                ix=s!=sid
                mf,ac,*_=cm_metrics(confusion(y[ix],p[ix].argmax(1),k))
                influence.append({'removed_study_id':sid,'removed_n':int((~ix).sum()),'remaining_macro_f1':mf,'remaining_accuracy':ac,'macro_f1_delta':mf-m['macro_f1']})
        joined=g.merge(records,on='record_id',how='left',suffixes=('','_record'),validate='one_to_one',indicator=True)
        assert joined.record_id.tolist()==g.record_id.tolist() and joined['_merge'].eq('both').all()
        for field in ['reactor','cell_type','ph_category','polymer_category','missing_pattern','catalyst_family']:
            if field not in joined:continue
            for val,sg in joined.fillna({field:'missing'}).groupby(field,dropna=False):
                ix=sg.index.to_numpy();subgroups.append(meta|{'subgroup_variable':field,'subgroup':str(val),'n_records':len(ix),'n_studies':sg.study_id.nunique(),'accuracy':correct[ix].mean(),'log_loss':ll[ix].mean(),'brier':bs[ix].mean()})
    allmet=pd.DataFrame(metrics);allmet.to_csv(r/'metrics_all_including_partial.csv',index=False);allmet.loc[~allmet.complete_oof].to_csv(r/'calibration_subset_metrics.csv',index=False);met=allmet.loc[allmet.complete_oof].copy();met.to_csv(r/'metrics.csv',index=False);pd.DataFrame(perclass).to_csv(r/'per_class.csv',index=False);pd.DataFrame(bins).to_csv(r/'reliability_bins.csv',index=False);pd.DataFrame(risk).to_csv(r/'risk_coverage.csv',index=False);pd.DataFrame(subgroups).to_csv(r/'subgroup_errors.csv',index=False);pd.DataFrame(studies).to_csv(r/'study_errors.csv',index=False);pd.DataFrame(influence).to_csv(r/'source_influence.csv',index=False)
    pairs=[];matched_metrics=[]
    for key,(g,y,p,ug,gcm,draws,ll,bs) in cache.items():
        split,model,feat,cal=key
        targets=[]
        if feat=='combined' and cal=='uncalibrated':
            targets=[(split,model,x,cal) for x in ['catalyst','conditions']]
            targets.append((split,'majority','none','uncalibrated'))
            if model in ['random_forest','hist_gradient_boosting']:targets.append((split,'logistic_regression','combined','uncalibrated'))
        if feat=='combined' and cal=='sigmoid':targets=[(split,model,feat,'uncalibrated')]
        for other in targets:
            if other not in cache:continue
            h,y2,p2,ug2,cm2,_,ll2,bs2=cache[other]
            if cal=='sigmoid' and g.record_id.tolist()!=h.record_id.tolist():
                ix=h.record_id.isin(g.record_id).to_numpy();h=h.loc[ix].reset_index(drop=True);y2=y2[ix];p2=p2[ix];ll2=ll2[ix];bs2=bs2[ix];source2=h.study_id.to_numpy();ug2=sorted(set(source2));cm2=np.stack([confusion(y2[source2==sid],p2[source2==sid].argmax(1),k) for sid in ug2])
            assert g.record_id.tolist()==h.record_id.tolist() and ug==ug2
            if cal=='sigmoid':
                for label,probs in [('sigmoid',p),('uncalibrated_matched',p2)]:
                    mm,_,_,_=scores(y,probs,g.study_id.to_numpy(),k);matched_metrics.append({'split':split,'model':model,'calibration':label,'feature_set':'combined','complete_oof':len(g)==len(records)}|mm)
            point=cm_metrics(gcm.sum(0))[0]-cm_metrics(cm2.sum(0))[0]
            delta=np.array([cm_metrics(gcm[x].sum(0))[0]-cm_metrics(cm2[x].sum(0))[0] for x in draws]);lo,hi=np.quantile(delta,[.025,.975])
            source=g.study_id.to_numpy(); sizes=np.array([(source==sid).sum() for sid in ug]); dl=np.array([(ll-ll2)[source==sid].sum() for sid in ug]); db=np.array([(bs-bs2)[source==sid].sum() for sid in ug]); ld=dl[draws].sum(1)/sizes[draws].sum(1); bd=db[draws].sum(1)/sizes[draws].sum(1); lli=np.quantile(ld,[.025,.975]); bsi=np.quantile(bd,[.025,.975])
            pairs.append({'delta_log_loss_ci_low':lli[0],'delta_log_loss_ci_high':lli[1],'delta_brier_ci_low':bsi[0],'delta_brier_ci_high':bsi[1],'split':split,'model':model,'left_feature_set':feat,'left_calibration':cal,'right_model':other[1],'right_feature_set':other[2],'right_calibration':other[3],'delta_macro_f1':point,'ci_low':lo,'ci_high':hi,'delta_log_loss':ll.mean()-ll2.mean(),'delta_brier':bs.mean()-bs2.mean(),'n_records':len(g),'n_studies':len(ug)})
    pd.DataFrame(pairs).to_csv(r/'paired_comparisons.csv',index=False)
    pd.DataFrame(matched_metrics).to_csv(r/'calibration_matched_metrics.csv',index=False)
    # All figures below consume only saved tables / prediction-derived data.
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':140})
    baseline=met.query("calibration == 'uncalibrated'")
    fig,axes=plt.subplots(1,2,figsize=(12,4),sharey=True)
    for ax,split in zip(axes,['random_condition','study']):
        sub=baseline[baseline.split==split];pivot=sub.pivot(index='model',columns='feature_set',values='macro_f1');pivot.plot.bar(ax=ax,ylim=(0,1),rot=20);ax.set_title({'random_condition':'Random split grouped by condition','study':'Held-out DOI groups'}[split]);ax.set_ylabel('Pooled macro-F1');ax.set_xlabel('')
    fig.tight_layout();fig.savefig(f/'model_feature_comparison.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4))
    focus=baseline.query("feature_set == 'combined' or model == 'majority'")
    for i,split in enumerate(['random_condition','study']):
        sub=focus[focus.split==split].sort_values('model');xx=np.arange(len(sub))+(i-.5)*.3
        ax.bar(xx,sub.macro_f1,width=.3,label=split)
        ax.vlines(xx,sub.macro_f1_ci_low,sub.macro_f1_ci_high,color='black',lw=1)
    ax.set_xticks(np.arange(len(sub)),sub.model,rotation=15);ax.set_ylabel('Macro-F1 (source bootstrap 95% interval)');ax.set_ylim(0,1);ax.legend();fig.tight_layout();fig.savefig(f/'split_comparison.png');plt.close(fig)
    rb=pd.read_csv(r/'reliability_bins.csv');rc=pd.read_csv(r/'risk_coverage.csv')
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for (model,cal),g in rb.query("split == 'study' and feature_set == 'combined' and complete_oof == True").groupby(['model','calibration']):axes[0].plot(g.confidence,g.accuracy,marker='o',ms=3,label=model+' '+cal)
    axes[0].plot([0,1],[0,1],'k--',lw=1);axes[0].set(xlim=(0,1),ylim=(0,1),xlabel='Mean top-label confidence',ylabel='Observed accuracy')
    for (model,cal),g in rc.query("split == 'study' and feature_set == 'combined' and complete_oof == True").groupby(['model','calibration']):axes[1].plot(g.coverage,g.accuracy,label=model+' '+cal)
    axes[1].set(xlim=(0,1.03),ylim=(0,1.03),xlabel='Retained coverage (exploratory)',ylabel='Accuracy');axes[1].legend(fontsize=6,loc='lower left');fig.tight_layout();fig.savefig(f/'reliability_risk.png');plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(10,4));matched_bins=[]
    for key,(g,y,p,ug,gcm,draws,ll,bs) in cache.items():
        if key[3]!='sigmoid':continue
        h,_,raw,*_=cache[(key[0],key[1],key[2],'uncalibrated')]
        ix=h.record_id.isin(g.record_id).to_numpy();raw=raw[ix]
        assert h.loc[ix].record_id.tolist()==g.record_id.tolist()
        for label,probs in [('sigmoid',p),('uncalibrated_matched',raw)]:
            confidence=probs.max(1);correct=probs.argmax(1)==y;bi=np.minimum((confidence*10).astype(int),9)
            for j in range(10):
                use=bi==j
                if use.any():matched_bins.append({'split':key[0],'model':key[1],'calibration':label,'bin':j,'n_records':int(use.sum()),'cohort_records':len(g),'cohort_studies':len(ug),'confidence':confidence[use].mean(),'accuracy':correct[use].mean()})
    mb=pd.DataFrame(matched_bins);mb.to_csv(r/'calibration_matched_bins.csv',index=False)
    for ax,split in zip(axes,['random_condition','study']):
        for (model,cal),g in mb.loc[mb.split==split].groupby(['model','calibration']):
            ax.plot(g.confidence,g.accuracy,marker='o',ms=3,label=model+' '+cal)
        ax.plot([0,1],[0,1],'k--',lw=1);ax.set(xlim=(0,1),ylim=(0,1),xlabel='Top-label confidence',ylabel='Accuracy',title=split+' matched calibration subset')
        ax.legend(fontsize=5)
    fig.tight_layout();fig.savefig(f/'calibration_matched_subsets.png');plt.close(fig)

    ck=('study','random_forest','combined','uncalibrated')
    if ck in cache:
        g,y,p,*_=cache[ck];cm=confusion(y,p.argmax(1),k);norm=cm/np.maximum(cm.sum(1,keepdims=True),1)
        fig,ax=plt.subplots(figsize=(6,5));im=ax.imshow(norm,vmin=0,vmax=1,cmap='Blues')
        for i in range(k):
            for j in range(k):ax.text(j,i,str(cm[i,j]),ha='center',va='center',color='white' if norm[i,j]>.6 else 'black')
        ax.set_xticks(range(k),classes,rotation=30);ax.set_yticks(range(k),classes);ax.set(xlabel='Predicted',ylabel='Recorded FE winner',title='Random forest, combined, held-out DOI groups');fig.colorbar(im,ax=ax,label='Within-class fraction');fig.tight_layout();fig.savefig(f/'confusion_matrix.png');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4));tab=records.groupby('target').agg(records=('record_id','size'),studies=('study_id','nunique')).reindex(classes);tab.plot.bar(ax=axes[0],rot=20);axes[0].set_title('Primary analysis coverage');records.study_id.value_counts().plot.bar(ax=axes[1],xticks=[]);axes[1].set(xlabel='DOI groups sorted by size',ylabel='Records',title='Source concentration');fig.tight_layout();fig.savefig(f/'data_coverage.png');plt.close(fig)
    meta={'predictions_sha256':hashlib.sha256((r/'predictions.csv').read_bytes()).hexdigest(),'bootstrap_replicates':a.bootstrap,'bootstrap_seed':cfg['seed']+991,'brier_definition':'mean(sum_k((p_k-one_hot_k)^2)); no division by K; range [0,2]','log_loss_epsilon':1e-15,'equal_study_definition':'one globally weighted confusion matrix, row weight 1/n_records_in_source','uncertainty':'Source cluster percentile bootstrap conditional on saved OOF predictions; no refitting; fold variability is not confidence interval','protocol_comparison':'descriptive; different training information, no causal/significance claim'}
    (r/'analysis_metadata.json').write_text(json.dumps(meta,indent=2));print(met.to_string(index=False))
if __name__=='__main__':main()
