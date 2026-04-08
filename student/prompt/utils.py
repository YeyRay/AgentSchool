import requests
import os
import json

current_dir = os.path.dirname(os.path.abspath(__file__))
json_file_path = os.path.join(current_dir, "..", "..", "config", "model.json")
try:
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    student_api_url = data.get('student_api_url')
except FileNotFoundError:
    print(f"The file {json_file_path} does not exist.")
except json.JSONDecodeError:
    print(f"Failed to decode JSON from the file {json_file_path}.")

API_KEY = os.getenv("SCHOOLAGENT_API_KEY")
API_URL = student_api_url

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def call_deepseek(messages, temperature=0.7, model="deepseek-chat", response_format=False):
    if not response_format:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
    else:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format":{
                "type": "json_object"
            }
        }
    response = requests.post(API_URL, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        raise Exception(f"API 请求失败：{response.status_code}\n{response.text}")
