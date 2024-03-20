from zulip_handler import zulipHandler
from database_handlers import notionHandler, zoteroHandler
from paper_handlers import arxiveHandler, openreviewHandler
from config import ZULIP_EMAIL, ZULIP_API_KEY, ZULIP_SITE, NOTION_TOKEN, NOTION_DATABASE_ID, ZOTERO_API_KEY, ZOTERO_GROUP_ID

if __name__ == "__main__":
    paper_handlers = [arxiveHandler(), openreviewHandler()]
    database_handlers = [notionHandler(auth_token=NOTION_TOKEN, database_id=NOTION_DATABASE_ID),
                         zoteroHandler(group_id=ZOTERO_GROUP_ID, api_key=ZOTERO_API_KEY)]

    zlp_handler = zulipHandler(email=ZULIP_EMAIL, api_key=ZULIP_API_KEY, site=ZULIP_SITE,
                               paper_handlers=paper_handlers, database_handlers=database_handlers)
    zlp_handler.run()
