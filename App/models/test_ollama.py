from pathlib import Path
import yaml

from langchain_ollama import ChatOllama


def load_llm_config():
    config_path = Path("configs/llm_config.yaml")

    with open(config_path, "r") as file:
        return yaml.safe_load(file)


def main():

    config = load_llm_config()

    model_name = config["llm"]["model_name"]
    temperature = config["llm"]["temperature"]

    print("=" * 50)
    print("TechAdmin - Ollama Test")
    print("=" * 50)

    print(f"Model : {model_name}")
    print()

    llm = ChatOllama(
        model=model_name,
        temperature=temperature,
    )

    query = input("Enter user query: ")

    system_prompt = """
    You are a TechAdmin IT Assistant.

    Analyze the user request.

    Extract:
    1. intent
    2. username
    3. email
    4. user_id

    Return only JSON.

    Example:

    {
      "intent": "password_reset",
      "username": "aman.gupta",
      "email": "",
      "user_id": ""
    }
    """

    final_prompt = f"""
    {system_prompt}

    User Request:
    {query}
    """

    response = llm.invoke(final_prompt)

    print("\nResponse:")
    print(response.content)


if __name__ == "__main__":
    main()