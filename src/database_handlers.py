from datetime import datetime
from pyzotero import zotero
from notion_client import Client

class zoteroHandler:

    def __init__(self, group_id, api_key, zotero_type='group'):
        self.client = zotero.Zotero(group_id, zotero_type, api_key)
        col = self.client.collections()
        self.collections = {c['data']['name']: c['key'] for c in col}

    def update_db(self, info):

        if info['stream'] not in self.collections:
            response = self.client.create_collections([{'name': info['stream']}])
            self.collections[info['stream']] = response['successful']['0']['key']

        items = self.client.everything(self.client.items())
        items = [item for item in items if 'data' in item and 'url' in item['data'] and info['link'] in item['data']['url']]
        if items:
            item = items[0]
            item_id = item['key']
            
            existing_tags = item['data'].get('tags', [])
            new_tags = [{'tag': info['sender']}]

            for new_tag in new_tags:
                if new_tag not in existing_tags:
                    existing_tags.append(new_tag)

            item['data']['tags'] = existing_tags

            existing_collections = item['data'].get('collections', [])
            new_collection = self.collections[info['stream']]

            if new_collection not in existing_collections:
                existing_collections.append(new_collection)

            item['data']['collections'] = existing_collections

            self.client.update_item(item)
            return_text = f"The item already existed in Zotero. I updated it."
        else:
            new_item = {
                'itemType': 'journalArticle',
                'title': info['title'],
                'creators': [{'creatorType': 'author', 'firstName': ' '.join(author.split(' ')[:-1]), 'lastName': author.split(' ')[-1]} for author in info['authors']],  # Adjust as needed
                'url': info['link'],
                'date': str(info['year']),
                'tags': [{'tag': info['sender']}],
                'abstractNote': info['abstract'],
                'collections': [self.collections[info['stream']]],
            }
            created_items = self.client.create_items([new_item])
            if created_items:
                item_id = created_items['successful']['0']['key']
                action_note_content = "This item was newly added to Zotero."
                action = "added"
                return_text = "I added the item to Zotero."
            if info.get('github_repo') is not None:
                linked_url = {
                    'itemType': 'attachment',
                    'linkMode': 'linked_url',
                    'title': 'Official GitHub',
                    'url': info['github_repo'],
                    'parentItem': item_id,
                }
                self.client.create_items([linked_url])
         
        additional_note = {
            'itemType': 'note',
            'parentItem': item_id,
            'note': f"{info['sender']} [{info['stream']}]: {info['message_content']}",
        }
        self.client.create_items([additional_note])
           
        return return_text



class notionHandler:

    def __init__(self, auth_token, database_id):
        self.client = Client(auth=auth_token)
        self.database_id = database_id

    def update_db(self, info):
        query_response = self.client.databases.query(**{"database_id": self.database_id, "filter": {"property": "Link", "url": {"equals": info['link']}}})
        if query_response['results']:
            page_id = query_response['results'][0]['id']
            current_page = self.client.pages.retrieve(page_id=page_id)
            existing_streams = [tag['name'] for tag in current_page['properties']['Zulip stream(s) source']['multi_select']]
            existing_people = [tag['name'] for tag in current_page['properties']['Shared on Zulip by']['multi_select']]
            existing_sources = [tag['name'] for tag in current_page['properties']['Source']['multi_select']]
            
            # Assuming 'Comments' is a rich text property, we need to handle it correctly.
            # Initialize existing comments as an empty string if the property doesn't exist or is empty.
            existing_comments = ""
            if 'Comments' in current_page['properties'] and 'rich_text' in current_page['properties']['Comments']:
                existing_comments = "".join([rt['plain_text'] for rt in current_page['properties']['Comments']['rich_text']])
            
            combined_streams = list(set(existing_streams + [info['stream']]))
            combined_people = list(set(existing_people + [info['sender']]))
            combined_sources = list(set(existing_sources + ['Zulip']))
            combined_comments = existing_comments + ("\n-----------------------\n" if existing_comments else '') + f"{info['sender']} [{info['stream']}]: {info['message_content']}"
            
            self.client.pages.update(
                page_id=page_id,
                properties={
                    "Zulip stream(s) source": {"multi_select": [{"name": tag} for tag in combined_streams]},
                    "Shared on Zulip by": {"multi_select": [{"name": tag} for tag in combined_people]},
                    "Source": {"multi_select": [{"name": tag} for tag in combined_sources]},
                    "Comments": {"rich_text": [{"text": {"content": combined_comments}}]},  # Update this line for rich text
                }
            )
            return f"The paper already existed in Notion from the following streams: {', '.join(existing_streams)}. I updated it."
        else:
            self.client.pages.create(
                parent={"database_id": self.database_id},
                properties={
                    "Name": {"title": [{"text": {"content": info['title']}}]},
                    "Link": {"url": info['link']},
                    "Code": {"url": info.get('github_repo')},
                    "Authors": {"rich_text": [{"type": "text", "text": {"content": " & ".join(info['authors'])}}]},
                    "Shared on Zulip by": {"multi_select": [{"name": info['sender']}]},
                    "Published": {"number": info['year']},
                    "Zulip stream(s) source": {"multi_select": [{"name": info['stream']}]},
                    "BibTeX": {"rich_text": [{"type": "text", "text": {"content": info['bibtex']}}]},
                    "Source": {"multi_select": [{"name": "Zulip"}]},
                    "Comments": {"rich_text": [{"text": {"content": f"{info['sender']} [{info['stream']}]: {info['message_content']}"}}]},
                }
            )
            return "I added the paper to Notion."
