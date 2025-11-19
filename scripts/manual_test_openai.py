from src.adapters.openai_client import OpenAIClient

client = OpenAIClient()

print(client.classify("Chcę zapisać się na jutro na crossfit", "pl"))
