from openai import OpenAI


def run_llm_indices(system_message, user_message, max_tokens=500, temperature=0.3, top_p=0.95):
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p
        )
        # Extract and print the generated text from the response
    print("----- ------ ------ LLM Response ----- ------ ------ ")
    print(response.choices[0].message.content)
    print("----- ------ ------ LLM Response end  ----- ------ ------ ")
    response = response.choices[0].message.content.strip()

    return response

