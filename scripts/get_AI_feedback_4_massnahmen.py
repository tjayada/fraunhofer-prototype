from groq import Groq
import os
import pandas
import requests
from pydantic import BaseModel
from typing import Literal
import json
from dotenv import load_dotenv
load_dotenv()

# load system prompt from file
with open("../prompts/system_prompt_massnahmen.txt", "r") as file:
    system_prompt_massnahmen = file.read()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
)



def load_survey_data(url):

    # Send a GET request to the URL
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Write the content to a CSV file
        with open('../data/table.csv', 'wb') as file:
            file.write(response.content)
        print("File downloaded successfully as '../data/table.csv'")
    else:
        print(f"Failed to download file. Status code: {response.status_code}")

    filename = '../data/table.csv'
    pd = pandas.read_csv(filename, sep=',')
    # drop first two rows
    pd = pd.drop(pd.index[0])
    pd = pd.drop(pd.index[0])

    # drop NaN columns
    pd = pd.dropna(axis=1, how='all')

    # save altered dataframe to csv
    pd.to_csv('../data/table.csv', index=False)
    return pd



def get_chat_completion(message_user, instructions):
    
    class Massnahme(BaseModel):
        title: str
        description: str
        priority: Literal["hoch", "mittel", "niedrig"]

        class Config:
            extra = 'forbid'  # Prevent extra fields
            validate_assignment = True  # Validate during assignment
            json_schema_extra = {
                "required": ["title", "description", "priority"]
            }
    
    class MassnahmenPlan(BaseModel):
        # This will be a dictionary with category names as keys and lists of massnahmen as values
        pass

    response = client.chat.completions.create(
        #model="moonshotai/kimi-k2-instruct", 
        model= "meta-llama/llama-4-maverick-17b-128e-instruct",
        messages=[
            {"role": "system", "content": system_prompt_massnahmen},
            {
                "role": "user", 
                "content": instructions + "\n" + message_user,
            },
        ],
        temperature=0.0,
        top_p=1.0,
        seed=42,  # Fixed seed
        max_tokens=2048,
        frequency_penalty=0.0,    # No frequency penalty
        presence_penalty=0.0,     # No presence penalty
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "massnahmen_plan", 
                "schema": {
                    "type": "object",
                    "properties": {
                        "einmalige_massnahmen": {"type": "array", "items": Massnahme.model_json_schema()},
                        "arbeitsplatz": {"type": "array", "items": Massnahme.model_json_schema()}
                    },
                    "additionalProperties": True
                }
            }
        }
    )
    print("--------------------------------")
    print(message_user, "\n")
    print(response.choices[0].message.content)

    # Parse the JSON response
    response_data = json.loads(response.choices[0].message.content)
    
    # Validate each massnahme in each category
    validated_plan = {}
    for category, massnahmen in response_data.items():
        validated_massnahmen = []
        for massnahme_data in massnahmen:
            try:
                validated_massnahme = Massnahme.model_validate(massnahme_data)
                validated_massnahmen.append(validated_massnahme.model_dump())
            except Exception as e:
                print(f"Error validating massnahme for {category}: {e}")
                print(f"Massnahme data: {massnahme_data}")
        validated_plan[category] = validated_massnahmen
    
    print(json.dumps(validated_plan, indent=2))
    return validated_plan


def main():
    
    url = os.getenv("SURVEY_URL")
    #pd = load_survey_data(url)

    # just load the csv file to save time
    pd = pandas.read_csv('../data/table.csv', sep=',')
    print(pd.head())

    instructions_massnahmen = open("../prompts/instructions_massnahmen.txt", "r").read()
    #message_user = "Explain the importance of fast language models"

    entire_data = ""
    for i in range(len(pd.columns)):
        column_name = pd.iloc[:, i].name
        column_values = pd.iloc[:, i].values
        
        #print(column_name)
        #print(column_values)
        #print("\n") 

        #message_user = f"{column_name} \n {column_values}"
        entire_data += f"{column_name} \n {column_values}"
        
    chat_completion = get_chat_completion(entire_data, instructions_massnahmen)
    #print(chat_completion)

    # write response into massnahmen.json file
    with open('../data/massnahmen.json', 'w') as file:
        json.dump(chat_completion, file)



if __name__ == "__main__":
    main()
