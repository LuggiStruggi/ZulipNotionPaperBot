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
    arxiv_ids = extract_arxiv_ids(message['content'])
    if arxiv_ids:
        for i, arxiv_id in enumerate(arxiv_ids):
            paper_info = get_arxiv_paper_info(arxiv_id)
            if paper_info:
                paper_info['sender'] = message['sender_full_name']
                paper_info['stream'] = message['display_recipient'] if message['type'] == 'stream' else None
                intro = f"Thank you for sharing, {message['sender_full_name']} 😎! Here is a short overview:\n" if i == 0 else ""
                numb = f"The {i+1}. paper you shared:\n" if len(arxiv_ids) > 1 else ""
                info = (f"- **Title**: {paper_info['title']}\n- **Authors**: {', '.join(paper_info['authors'])}\n"
                        f"- **Abstract**: {paper_info['abstract']}\n- **Link**: {paper_info['link']}")
                send_message_to_zulip(intro+numb+info, message)
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
    return arxiv_ids

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

def main():
    client.call_on_each_message(lambda message: handle_message(message))

if __name__ == "__main__":
    main()
