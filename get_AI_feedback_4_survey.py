from groq import Groq
import os
import pandas
import requests
from dotenv import load_dotenv
load_dotenv()

# load system prompt from file
with open("system_prompt.txt", "r") as file:
    system_prompt = file.read()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
)



def load_survey_data(url):

    # Send a GET request to the URL
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Write the content to a CSV file
        with open('table.csv', 'wb') as file:
            file.write(response.content)
        print("File downloaded successfully as 'table.csv'")
    else:
        print(f"Failed to download file. Status code: {response.status_code}")

    filename = 'table.csv'
    pd = pandas.read_csv(filename, sep=',')
    # drop first two rows
    pd = pd.drop(pd.index[0])
    pd = pd.drop(pd.index[0])

    # drop NaN columns
    pd = pd.dropna(axis=1, how='all')

    # save altered dataframe to csv
    pd.to_csv('table.csv', index=False)
    return pd



def get_chat_completion(message_user, instructions):
    
    chat_completion = client.chat.completions.create(
        messages=[
            # Set an optional system message. This sets the behavior of the
            # assistant and can be used to provide specific instructions for
            # how it should behave throughout the conversation.
            {
                "role": "system",
                "content": system_prompt
            },
            # Set a user message for the assistant to respond to.
            {
                "role": "user",
                "content": instructions + "\n" + message_user,
            }
        ],

        # The language model which will generate the completion.
        model="llama-3.3-70b-versatile"
    )

    return chat_completion.choices[0].message.content


def main():
    
    url = os.getenv("SURVEY_URL")
    #pd = load_survey_data(url)

    # just load the csv file to save time
    pd = pandas.read_csv('table.csv', sep=',')
    print(pd.head())

    instructions = open("instructions.txt", "r").read()
    #message_user = "Explain the importance of fast language models"
    #chat_completion = get_chat_completion(message_user, instructions)
    #print(chat_completion)



if __name__ == "__main__":
    main()

