import zulip
import pytz
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from notion_client import Client
from config import ZULIP_EMAIL, ZULIP_API_KEY, ZULIP_SITE, NOTION_TOKEN, NOTION_DATABASE_ID

client = zulip.Client(email=ZULIP_EMAIL, api_key=ZULIP_API_KEY, site=ZULIP_SITE)
notion = Client(auth=NOTION_TOKEN)
local_timezone = pytz.timezone('Europe/Berlin')

def check_exists(url):
    query_results = notion.databases.query(database_id=NOTION_DATABASE_ID, filter={"property": "URL", "url": {"equals": url}})
    return len(query_results["results"]) > 0

def add_link_to_notion(info):
    if check_exists(info['link']):
        return "This paper already exists in Notion."
    current_datetime = datetime.now(local_timezone)
    formatted_datetime = current_datetime.isoformat()     
    notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties={
        "Name": {"title": [{"text": {"content": info['title']}}]},
        "URL": {"url": info['link']},
        "Code": {"url": info['github_repo']},
        "Authors": {"rich_text": [{"text": {"content": ", ".join(info['authors'])}}]},
        "Shared by": {"rich_text": [{"text": {"content": info['sender']}}]},
        "Published": {"date": {"start": info['publish_date'], "end": None}},
        "Shared": {"date": {"start": formatted_datetime, "end": None}},
        "Stream": {"multi_select": [{"name": info['stream']}]}
    })
    return "I added the paper to Notion."

def handle_message(message):
    if message['sender_email'] == ZULIP_EMAIL:
        return
    paper_ids = extract_paper_ids(message['content'])
    if paper_ids:
        for i, (id_type, paper_id) in enumerate(paper_ids):
            if id_type == 'arxiv':
                paper_info = get_arxiv_paper_info(paper_id)
            elif id_type == 'openreview':
                paper_info = get_openreview_paper_info(paper_id)

            if paper_info:
                paper_info['github_repo'] = get_github_repo(paper_id) if id_type == 'arxiv' else None 
                paper_info['sender'] = message['sender_full_name']
                paper_info['stream'] = message['display_recipient'] if message['type'] == 'stream' else None
                intro = f"Thank you for sharing, {message['sender_full_name']} 😎! Here is a short overview:\n" if i == 0 else ""
                numb = f"The {i+1}. paper you shared:\n" if len(paper_ids) > 1 else ""
                info = (f"- **Title**: {paper_info['title']}\n- **Authors**: {', '.join(paper_info['authors'])}\n"
                        f"- **Abstract**: {paper_info['abstract']}\n- **Link**: {paper_info['link']}")
                github = f"\n- **Official GitHub**: {paper_info['github_repo']}" if paper_info['github_repo'] is not None else ''
                send_message_to_zulip(intro+numb+info+github, message)
                send_message_to_zulip(add_link_to_notion(paper_info), message)

def send_message_to_zulip(response_message, message_data):
    request = {
               "type": message_data['type'], "to": message_data['sender_email'] if message_data['type'] == 'private' else message_data['display_recipient'],
               "subject": message_data.get('subject', ''),
               "content": response_message
              }
    client.send_message(request)

def extract_arxiv_ids(message_content):
    arxiv_regex = r'(arXiv:)?(\d{4}\.\d{5})|(https?://arxiv\.org/abs/(\d{4}\.\d{5}))'
    matches = re.findall(arxiv_regex, message_content)
    arxiv_ids = [match[1] if match[1] else match[3] for match in matches if match[1] or match[3]]
    return [("arxiv", i) for i in arxiv_ids]

def extract_openreview_ids(message_content):
    openreview_regex = r'https?://openreview\.net/(forum|pdf)\?id=([A-Za-z0-9_]+)'
    matches = re.findall(openreview_regex, message_content)
    openreview_ids = [match[1] for match in matches]
    return [("openreview", i) for i in openreview_ids]

def extract_paper_ids(message_content):
    arxiv_ids = extract_arxiv_ids(message_content)
    openreview_ids = extract_openreview_ids(message_content)
    return arxiv_ids + openreview_ids 

def get_arxiv_paper_info(arxiv_id):
    url = f'http://export.arxiv.org/api/query?id_list={arxiv_id}'
    response = requests.get(url)
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        entry = root.find('{http://www.w3.org/2005/Atom}entry')
        if entry:
            title = entry.find('{http://www.w3.org/2005/Atom}title').text.strip()
            authors = [author.find('{http://www.w3.org/2005/Atom}name').text for author in entry.findall('{http://www.w3.org/2005/Atom}author')]
            abstract = entry.find('{http://www.w3.org/2005/Atom}summary').text.strip()
            link = entry.find('{http://www.w3.org/2005/Atom}id').text
            publish_date = entry.find('{http://www.w3.org/2005/Atom}published').text
            return {"title": title, "authors": authors, "abstract": abstract, "link": link, "publish_date": publish_date}


def get_openreview_paper_info(openreview_id):
    api_url = f"https://api2.openreview.net/notes?id={openreview_id}"
    response = requests.get(api_url) 
    if response.status_code == 200:
        paper_data = response.json().get('notes', [])
        if paper_data:
            paper = paper_data[0]
            title = paper['content']['title']['value']
            authors = paper['content']['authors']['value']
            abstract = paper['content']['abstract']['value']
            link = f"https://openreview.net/forum?id={openreview_id}"
            publish_date = datetime.utcfromtimestamp(paper.get('cdate') / 1000).isoformat() + 'Z'
            return {"title": title, "authors": authors, "abstract": abstract, "link": link, "publish_date": publish_date}


# get the code of the paper

def get_all_repositories(paper_id):
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

def get_official_repositories(paper_id):
    all_repositories = get_all_repositories(paper_id)
    official_repos = [repo for repo in all_repositories if repo.get('is_official') == True]
    return official_repos

def get_github_repo(arxiv_id):
    arxiv_id = arxiv_id.split("v")[0]
    url = f"https://paperswithcode.com/api/v1/papers/?arxiv_id={arxiv_id}"
    response = requests.get(url)
    papers = response.json()
    if response.status_code == 200 and papers['results']:
        paper_id = papers['results'][0]['id']
        official_repos = get_official_repositories(paper_id)
        if official_repos:
            github_url = official_repos[0]['url']
            return github_url

def main():
    client.call_on_each_message(lambda message: handle_message(message))

if __name__ == "__main__":
    main()
