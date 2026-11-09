import urllib.request,urllib.error,json,concurrent.futures
from pathlib import Path
p=Path('work/source_a')
urls={
'user':'https://api.github.com/users/alpertap74/repos?per_page=100',
'pdf':'https://onlinelibrary.wiley.com/doi/pdf/10.1155/er/2400202',
'xml':'https://onlinelibrary.wiley.com/doi/full-xml/10.1155/er/2400202',
'wiley_assets':'https://onlinelibrary.wiley.com/doi/suppl/10.1155/er/2400202/supinfo/er2400202-sup-0001-suppinfo.xlsx',
'openalex':'https://api.openalex.org/works/https://doi.org/10.1155/er/2400202',
'crossref_transform':'https://api.crossref.org/works/10.1155/er/2400202/transform/application/vnd.crossref.unixsd+xml',
'wayback':'https://web.archive.org/cdx/search/cdx?url=github.com/alpertap74/CO2-electrolyzer_2003_2025/*&output=json&filter=statuscode:200&collapse=urlkey',
'raw_main':'https://raw.githubusercontent.com/alpertap74/CO2-electrolyzer_2003_2025/main/database_CO2reduction_2003_2025.xlsx',
'raw_master':'https://raw.githubusercontent.com/alpertap74/CO2-electrolyzer_2003_2025/master/database_CO2reduction_2003_2025.xlsx',
'zenodo':'https://zenodo.org/api/records?q=2400202&size=10',
'figshare':'https://api.figshare.com/v2/articles?resource_doi=10.1155/er/2400202',
}
def run(t):
 k,u=t
 try:
  r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=35);d=r.read();s=r.status;f=r.url
 except urllib.error.HTTPError as e:d=e.read();s=e.code;f=e.url
 except Exception as e:return {'key':k,'url':u,'error':repr(e)}
 (p/(k+'.bin')).write_bytes(d)
 return {'key':k,'url':u,'final_url':f,'status':s,'bytes':len(d),'preview':d[:200].decode(errors='replace')}
rs=list(concurrent.futures.ThreadPoolExecutor(6).map(run,urls.items()))
(p/'additional_access.json').write_text(json.dumps(rs,indent=2))
for r in rs:print(r)
