import zulip
from datetime import datetime
import re
import threading

def replace_single_dollar(s):
    def repl(match):
        repl.counter += 1
        if repl.counter % 2 == 1:
            return '$$'
        else:
            return '$$&#x200B;'
    repl.counter = 0

    pattern = r'(?<!\$)\$(?!\$)'
    return re.sub(pattern, repl, s)


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

    def info_to_message(self, title, authors, abstract, link, github=None):
        message = f"``` spoiler {replace_single_dollar(title)}\n- **Authors**: {', '.join(authors)}\n- **Abstract**: {replace_single_dollar(abstract)}\n- **Link**: {link}\n"
        if github is not None:
            message += f"- **Official GitHub**: {github}\n"
        message += "```"
        return message

    def try_update_databases(self, paper_info):
        response_msg = ""
        for handler_wrapper in self.database_handlers:
            try:
                update_result = handler_wrapper.update_db(paper_info)
                response_msg += "\n" + update_result
            except Exception as e:
                print(f"Warning: Failed to update database {handler_wrapper.handler_class.__name__}. Exception: {e}")
                response_msg += f"\nFailed to update {handler_wrapper.handler_class.__name__}."
                continue
        return response_msg

    def handle_message(self, message):
        if message['sender_email'] == self.email:
            return

        message_filtered = self.filter_zulip_quotes(message['content'])

        # Extract paper IDs from all paper handlers.
        all_paper_ids = []
        for paper_handler in self.paper_handlers:
            ids = paper_handler.extract_ids(message_filtered)
            all_paper_ids.extend(ids)

        if not all_paper_ids:
            return

        # Process each paper id separately.
        for paper_handler in self.paper_handlers:
            paper_ids = paper_handler.extract_ids(message_filtered)
            for paper_id in paper_ids:
                # Send an initial message for this paper ID.
                initial_feedback = (
                    f"*Retrieving paper information...*"
                )
                request = {
                    "type": message['type'],
                    "to": message['sender_email'] if message['type'] == 'private' else message['display_recipient'],
                    "subject": message.get('subject', ''),
                    "content": initial_feedback
                }
                response = self.client.send_message(request)
                initial_message_id = response.get('id')

                try:
                    paper_info = paper_handler.get_info(paper_id)
                except Exception as e:
                    error_feedback = f"Failed to retrieve info for paper ID {paper_id}. Error: {e}"
                    self.client.update_message({"message_id": initial_message_id, "content": error_feedback})
                    continue

                if not paper_info:
                    no_info_feedback = f"No info returned for ID {paper_id}."
                    self.client.update_message({"message_id": initial_message_id, "content": no_info_feedback})
                    continue

                detailed_info = self.info_to_message(
                    paper_info['title'],
                    paper_info['authors'],
                    paper_info['abstract'],
                    paper_info['link'],
                    paper_info.get('github')
                )
                detailed_message = f"{message['sender_full_name']} shared:\n{detailed_info}"
                self.client.update_message({"message_id": initial_message_id, "content": detailed_message})

                def update_and_notify(info, orig_message):
                    info['sender'] = orig_message['sender_full_name']
                    info['stream'] = (orig_message['display_recipient']
                                      if orig_message['type'] == 'stream' else None)
                    info['message_content'] = orig_message['content']

                    db_initial_feedback = "*Updating databases...*"
                    db_request = {
                        "type": orig_message['type'],
                        "to": orig_message['sender_email'] if orig_message['type'] == 'private' else orig_message['display_recipient'],
                        "subject": orig_message.get('subject', ''),
                        "content": db_initial_feedback
                    }
                    db_response = self.client.send_message(db_request)
                    db_message_id = db_response.get('id')

                    update_result = self.try_update_databases(info)
                    self.client.update_message({
                        "message_id": db_message_id,
                        "content": update_result
                    })

                threading.Thread(target=update_and_notify, args=(paper_info, message)).start()


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
                if out:
                    out.pop(-1)
                i += 1
                while i < n_lines and '`'*ticks not in lines[i]:
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
