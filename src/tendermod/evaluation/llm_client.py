from openai import OpenAI
from dotenv import load_dotenv

from tendermod.evaluation.prompts import basic_comparation_system_prompt, basic_comparation_user_prompt

load_dotenv()
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


def run_llm_indicators_comparation(var1, var2, general_info, max_tokens=1000, temperature=0.0, top_p=1):

    client = OpenAI()
    user_prompt = basic_comparation_user_prompt
    user_prompt = user_prompt.replace("{general_info}", general_info)
    user_prompt = user_prompt.replace("{exp1}", var1)
    user_prompt = user_prompt.replace("{exp2}", var2)

    print (f"System Propmt: \n { basic_comparation_system_prompt}")
    print (f"User Propmt: \n { user_prompt}")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": basic_comparation_system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p
        )
        # Extract and print the generated text from the response
    return response.choices[0].message.content





