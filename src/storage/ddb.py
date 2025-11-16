import os
from ..common.aws import ddb_resource

class MessagesRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_MESSAGES", "Messages"))
    def put(self, item: dict): self.table.put_item(Item=item)

class ConversationsRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_CONVERSATIONS", "Conversations"))
    def get(self, pk: str): return self.table.get_item(Key={"pk": pk}).get("Item")
    def put(self, item: dict): self.table.put_item(Item=item)
    def delete(self, pk: str): self.table.delete_item(Key={"pk": pk})
    
class MembersIndexRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_MEMBERS_INDEX", "MembersIndex"))
    def find_by_phone(self, tenant_id: str, phone: str):
        # np. query po pk = f"{tenant_id}#{member_id}", secondary index po phone
        ...
