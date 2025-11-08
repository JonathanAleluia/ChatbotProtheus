from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",
    google_api_key="AIzaSyAZL2PWZ9cJkwOSJyjdstodZldUbCgZ19Y"
)

print("Conexão bem-sucedida ✅")
