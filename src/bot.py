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
        "Shared": {"date": {"start": formatted_datetime, "end": None}}
    })
    return "I added the paper to Notion."

def handle_message(message):
    if message['sender_email'] == ZULIP_EMAIL:
        return
    arxiv_id = extract_arxiv_id(message['content'])
    if arxiv_id:
        paper_info = get_arxiv_paper_info(arxiv_id)
        if paper_info:
            paper_info['sender'] = message['sender_full_name']
            response_message = (f"Thank you for sharing, {message['sender_full_name']} 😎! Here is a short overview:\n"
                               f"- **Title**: {paper_info['title']}\n- **Authors**: {', '.join(paper_info['authors'])}\n"
                               f"- **Abstract**: {paper_info['abstract']}\n- **Link**: {paper_info['link']}")
            send_message_to_zulip(response_message, message)
            send_message_to_zulip(add_link_to_notion(paper_info), message)

def send_message_to_zulip(response_message, message_data):
    request = {
               "type": message_data['type'], "to": message_data['sender_email'] if message_data['type'] == 'private' else message_data['display_recipient'],
               "subject": message_data.get('subject', ''),
               "content": response_message
              }
    client.send_message(request)

def extract_arxiv_id(message_content):
    arxiv_regex = r'(arXiv:)?(\d{4}\.\d{5})|(https?://arxiv\.org/abs/(\d{4}\.\d{5}))'
    match = re.search(arxiv_regex, message_content)
    return match.group(2) or match.group(4) if match else None

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
