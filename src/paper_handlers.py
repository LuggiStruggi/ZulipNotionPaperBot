import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime


def paper_info_to_bibtex(paper_info, is_arxive=False):
    year = str(datetime.fromisoformat(paper_info['publish_date'].rstrip('Z')).year)
    bib_id = paper_info['authors'][0].split(' ')[1].lower() + year + re.sub(r'[^a-zA-Z]*$', '', paper_info['title'].split(' ')[0].lower())
    bib = (f"@misc{{{bib_id},\n"
           f"      title = {{{paper_info['title']}}},\n"
           f"      author = {{{' and '.join(', '.join([a.split()[-1], ' '.join(a.split()[:-1])]) for a in paper_info['authors'])}}},\n"
           f"      year = {{{year}}},\n"
           f"      url = {{{paper_info['link']}}}")
    if is_arxive:
        add = (",\n"
               f"      eprint = {{{paper_info['id']}}},\n"
               f"      archivePrefix = {{arXiv}},\n"
               f"      primaryClass = {{{paper_info['category']}}}\n")
    else:
        add = "\n"
    return bib + add + "}" 


class paperHandler:

    def __init__(self):
        self.log = []

    def flush_log(self):
        out = self.log
        self.log = []
        return out


class arxiveHandler(paperHandler):

    def extract_ids(self, message_content):
        arxiv_regex = r'\b(?:arXiv:)?(\d{4}\.\d{5})\b|https?://arxiv\.org/abs/(\d{4}\.\d{5})'
        matches = re.findall(arxiv_regex, message_content)
        arxiv_ids = [arxiv_id for match in matches for arxiv_id in match if arxiv_id]
        return arxiv_ids

    def get_info(self, arxiv_id):
        url = f'http://export.arxiv.org/api/query?id_list={arxiv_id}'
        response = requests.get(url)
        if response.status_code != 200:
            self.log.append(response)
            return
        root = ET.fromstring(response.content)
        entry = root.find('{http://www.w3.org/2005/Atom}entry')
        if entry:
            title = entry.find('{http://www.w3.org/2005/Atom}title').text.strip().replace("\n", " ")
            authors = [author.find('{http://www.w3.org/2005/Atom}name').text for author in entry.findall('{http://www.w3.org/2005/Atom}author')]
            abstract = entry.find('{http://www.w3.org/2005/Atom}summary').text.strip().replace("\n", " ")
            link = entry.find('{http://www.w3.org/2005/Atom}id').text
            publish_date = entry.find('{http://www.w3.org/2005/Atom}published').text
            category_element = entry.find('{http://www.w3.org/2005/Atom}category')
            if category_element is not None:
                primary_category = category_element.attrib.get('term', '')
            else:
                primary_category = None
            year = datetime.fromisoformat(publish_date.rstrip('Z')).year
            info = {"title": title, "authors": authors, "abstract": abstract, "link": link, "publish_date": publish_date,
                    "year": year, "id": arxiv_id, "category": primary_category, "github_repo": self.get_github_url(arxiv_id)}
            bibtex = paper_info_to_bibtex(info, is_arxive=False)
            info['bibtex'] = bibtex
            return info


    def get_all_repositories(self, paper_id):
        base_url = f"https://paperswithcode.com/api/v1/papers/{paper_id}/repositories/"
        repositories = []
        while base_url:
            response = requests.get(base_url)
            if response.status_code == 200:
                data = response.json()
                repositories.extend(data.get('results', []))
                base_url = data.get('next')
            else:
                break
        return repositories

    def get_official_repositories(self, paper_id):
        all_repositories = self.get_all_repositories(paper_id)
        official_repos = [repo for repo in all_repositories if repo.get('is_official') == True]
        return official_repos

    def get_github_url(self, arxiv_id):
        arxiv_id = arxiv_id.split("v")[0]
        url = f"https://paperswithcode.com/api/v1/papers/?arxiv_id={arxiv_id}"
        response = requests.get(url)
        papers = response.json()
        if response.status_code != 200:
            self.log.append(response)
            return 
        if papers['results']:
            paper_id = papers['results'][0]['id']
            official_repos = self.get_official_repositories(paper_id)
            if official_repos:
                github_url = official_repos[0]['url']
                return github_url


class openreviewHandler(paperHandler):

    def extract_ids(self, message_content):
        openreview_regex = r'https?://openreview\.net/(forum|pdf)\?id=([A-Za-z0-9_]+)'
        matches = re.findall(openreview_regex, message_content)
        openreview_ids = [match[1] for match in matches]
        return openreview_ids

    def get_info(self, openreview_id):
        api2 = True
        api_url = f"https://api2.openreview.net/notes?id={openreview_id}"
        response = requests.get(api_url)
        if response.status_code != 200:
            api2 = False
            api_url = f"https://api.openreview.net/notes?id={openreview_id}"
            response = requests.get(api_url)
            if response.status_code != 200:
                self.log.append(response)
                return
        paper_data = response.json().get('notes', [])
        if paper_data:
            paper = paper_data[0]
            title = paper['content']['title']['value'] if api2 else paper['content']['title'].replace("\n" " ")
            authors = paper['content']['authors']['value'] if api2 else paper['content']['authors']
            abstract = paper['content']['abstract']['value'].replace("\n", " ") if api2 else paper['content']['abstract'].replace("\n", " ")
            link = f"https://openreview.net/forum?id={openreview_id}"
            publish_date = datetime.utcfromtimestamp(paper.get('cdate') / 1000).isoformat() + 'Z'
            year = datetime.fromisoformat(publish_date.rstrip('Z')).year
            info = {"title": title, "authors": authors, "abstract": abstract, "link": link,
                    "publish_date": publish_date, "year": year}
            bibtex = paper_info_to_bibtex(info, is_arxive=False)
            info['bibtex'] = bibtex
            return info
