import os
from dotenv import load_dotenv
import google.generativeai as genai

# Mimic the path logic in main.py
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
print(f"Looking for .env at: {env_path}")
load_dotenv(env_path)

print("Environment Variables Check:")
print(f"GOOGLE_API_KEY env var: {'Found' if os.getenv('GOOGLE_API_KEY') else 'Not Found'}")
print(f"NEXT_PUBLIC_GOOGLE_API_KEY env var: {'Found' if os.getenv('NEXT_PUBLIC_GOOGLE_API_KEY') else 'Not Found'}")

final_key = os.getenv("GOOGLE_API_KEY") or os.getenv("NEXT_PUBLIC_GOOGLE_API_KEY")
print(f"Resolved Key: {'Found' if final_key else 'Not Found'}")

if final_key:
    print(f"Key starts with: {final_key[:5]}...")
    try:
        genai.configure(api_key=final_key)
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content("Hello")
        print("Gemini Test Response:", response.text)
    except Exception as e:
        print("Gemini Test Error:", e)
else:
    print("Cannot test Gemini without key.")
