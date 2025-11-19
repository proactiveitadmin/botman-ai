from src.adapters.jira_client import JiraClient

client = JiraClient()
print(client.create_ticket("Test z dev", "To jest testowy ticket", "default"))
