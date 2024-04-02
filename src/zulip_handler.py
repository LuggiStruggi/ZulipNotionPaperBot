import zulip
from datetime import datetime
import re

class zulipHandler:

    def __init__(self, email, api_key, site, paper_handlers = None, database_handlers = None):
        self.client = zulip.Client(email=email, api_key=api_key, site=site)
        self.email = email
        self.paper_handlers = paper_handlers
        if self.paper_handlers is None:
            self.paper_handlers = []
        
        self.database_handlers = database_handlers
        if self.database_handlers is None:
            self.database_handlers = []



    def handle_message(self, message):
        if message['sender_email'] == self.email:
            return
        message_filtered = self.filter_zulip_quotes(message['content'])
        for paper_handler in self.paper_handlers:
            paper_ids = paper_handler.extract_ids(message_filtered)
            for i, paper_id in enumerate(paper_ids):
                try:
                    paper_info = paper_handler.get_info(paper_id)
                except:
                    print("Wasn't able to receive paper info")
                    continue
                if paper_info:

                    paper_info['sender'] = message['sender_full_name']
                    paper_info['stream'] = message['display_recipient'] if message['type'] == 'stream' else None
                    paper_info['message_content'] = message['content']

                    intro = f"Thank you for sharing, {message['sender_full_name']} 😎! Here is a short overview:\n" if i == 0 else ""
                    number = f"The {i+1}. paper you shared:\n" if len(paper_ids) > 1 else ""
                    info = (f"- **Title**: {paper_info['title']}\n- **Authors**: {', '.join(paper_info['authors'])}\n"
                            f"- **Abstract**: {paper_info['abstract']}\n- **Link**: {paper_info['link']}")
                    github = f"\n- **Official GitHub**: {paper_info['github_repo']}" if 'github_repo' in paper_info and paper_info['github_repo'] is not None else ''

                    added_link = "\n"
                    for database_handler in self.database_handlers:
                        try:
                            added_link += "\n" + database_handler.update_db(paper_info)
                        except:
                            print("Wasn't able to add paper to database")
                            continue

                    self.send_message_to_zulip(intro+number+info+github+added_link, message)


    def send_message_to_zulip(self, response_message, message_data):
        request = {
                   "type": message_data['type'], "to": message_data['sender_email'] if message_data['type'] == 'private' else message_data['display_recipient'],
                   "subject": message_data.get('subject', ''),
                   "content": response_message
                  }
        self.client.send_message(request)


    def run(self):
        self.client.call_on_each_message(lambda message: self.handle_message(message))

    def count_backticks_in_quote(self, line):
        match = re.match(r'^(`+)(quote)', line)
        return len(match.group(1)) if match else 0


    def filter_zulip_quotes(self, content):
        lines = content.split('\n')
        out = []
        n_lines = len(lines)
        i = 0
        while i < n_lines:
            ticks = self.count_backticks_in_quote(lines[i])
            if ticks:
                out.pop(-1)
                i += 1
                while '`'*ticks not in lines[i]:
                    i += 1
            else:
                out.append(lines[i])
            i += 1
        return "\n".join(out)


    def paper_info_to_bibtex(self, paper_info):
        year = str(datetime.fromisoformat(paper_info['publish_date'].rstrip('Z')).year)
        bib_id = paper_info['authors'][0].split(' ')[1].lower() + year + re.sub(r'[^a-zA-Z]*$', '', paper_info['title'].split(' ')[0].lower())
        bib = (f"@misc{{{bib_id},\n"
               f"      title = {{{paper_info['title']}}},\n"
               f"      author = {{{' and '.join(', '.join([a.split()[-1], ' '.join(a.split()[:-1])]) for a in paper_info['authors'])}}},\n"
               f"      year = {{{year}}},\n"
               f"      url = {{{paper_info['link']}}}")
        if paper_info['type'] == 'arxiv':
            add = (",\n"
                   f"      eprint = {{{paper_info['id']}}},\n"
                   f"      archivePrefix = {{arXiv}},\n"
                   f"      primaryClass = {{{paper_info['category']}}}\n")
        else:
            add = "\n"
        return bib + add + "}" 
