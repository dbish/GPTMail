from asyncio import run, wait_for
import mailparser
import aiohttp
import aioimaplib
from config_reader import HOST, USER, PASSWORD, OPEN_AI_SECRET_KEY
from openai import OpenAI
import json
from string import Template
from email_reply_parser import EmailReplyParser

import smtplib
# Import the email modules we'll need
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

ASSISTANTS = {
    'captain': 'asst_nCFYjknlZW8oGxPw7b9MnrDn',
    'steve': 'asst_fXiEVWUohKAlfFipRwfZRtNV',
    'librarian':'asst_McYq9xd4R8S7avhGxlfeO6aV'
}

PREAMBLE = Template('''
    You are responding to emails from inquiring children. You'll be reading in mostly
    html and should respond with html as well. Responses should be written for children
    and where possible provide inline images to explain a concept. Emails will show
    the entire thread where there can be responses from you (askgptmail@gmail.com)
    and the friendly kid you're responding to. Keep all responses G rated and 
    friendly, be nice and don't answer if you get questions that are not kid appropriate.
    The kid you're interacting with is named $full_name based on their email address
    but if they tell you a different name, use that instead in responses. Be whimsical
    and have fun with responses, throw in a dr.seuss like rhyme occasionally 
    where it can fit.
''')

try:
    openai_api_key = OPEN_AI_SECRET_KEY
except:
    print("OpenAI key not found")

OPENAI_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer " + openai_api_key,
}

async def openai_get_assistant_response(assistant_name, user_message, prev_messages=None):
    client = OpenAI(api_key=openai_api_key)
    thread = client.beta.threads.create()
    assistant_id = ASSISTANTS[assistant_name]

    #todo: make previous messages useful

    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message
    )
    print(message)
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id,
    )

    while run.status != "completed":
        keep_retrieving_run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )
        print(f"Run status: {keep_retrieving_run.status}")

        if keep_retrieving_run.status == "completed":
            print("\n")
            break

    # Retrieve messages added by the Assistant to the thread
    all_messages = client.beta.threads.messages.list(
        thread_id=thread.id
    )

    print(f"ASSISTANT: {all_messages.data[0].content[0].text.value}")
    return all_messages.data[0].content[0].text.value

async def openai_get_chat_completion(prompt,model='gpt-3.5-turbo-16k-0613',temp=0.3,max_tokens=256,timeout=20, validation_func=lambda x:x, prev_messages=None):
    url = "https://api.openai.com/v1/chat/completions"
    if prev_messages:
        messages = prev_messages
    else:
        messages = []
    messages.append(
        {
            "role": "user",
            "content": prompt
        })
    
    print(messages)

    params = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0
        })
    
    try:
        print("Querying OpenAI for chat completion...")
        async with aiohttp.ClientSession(headers=OPENAI_HEADERS) as session:
            async with session.post(url, data=params, timeout=aiohttp.ClientTimeout(total=timeout)) as response:

                if response.status != 200:
                    print(f"OpenAI returned non-success code: {response.status}")
                    return False, None
                
                response_json = await response.json()
                result = response_json['choices'][0]['message']['content']

    except Exception as e:
        print(f'Exception raised during OpenAI call: {repr(e)}')
        return False, None

    print("OpenAI returned success")
    
    try:
        validated_result = validation_func(result)
    except Exception as e:
        print(f'OpenAI result conversion failed: {repr(e)}')
        return False, None
    
    return True, validated_result

async def respondEmail(from_email, to_email, response, orig_email):
    print(from_email)
    from_addr = from_email[0][1]
    to_addr = to_email[0][1]
    print('to: ' + to_addr)
    thread_id = orig_email.message_id
    thread_subject = orig_email.subject
    msg = EmailMessage()
    msg = MIMEMultipart('alternative')
    html_message = MIMEText(response, 'html')
    msg.attach(html_message)

    if 're:' not in thread_subject.lower():
        thread_subject = 'Re: '+ thread_subject
    msg['Subject'] = thread_subject

    msg['From'] = from_addr
    msg['To'] = to_addr
    print(to_addr)
    msg.add_header('In=Reply-To', thread_id)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server:
        smtp_server.login(USER, PASSWORD)
        smtp_server.send_message(msg)


async def processUnread(to, user_info, body):
    name = user_info[0][0]
    all_body = body[0]

    reply = EmailReplyParser.parse_reply(all_body)
    thread_history = all_body[len(reply)::]

    
    assistant_name = to[0][1].split('@')[0]
    print(assistant_name)
    if assistant_name not in ASSISTANTS:
        return None
    response = await openai_get_assistant_response(assistant_name, reply, prev_messages=thread_history)
    return response

async def imap_loop(host, user, password) -> None:
    imap_client = aioimaplib.IMAP4_SSL(host=host, timeout=30)
    await imap_client.wait_hello_from_server()

    await imap_client.login(user, password)
    await imap_client.select('INBOX')

    while True:
        response = await imap_client.search('(UNSEEN)')
        unread_uids = response.lines[0].split()
        unread_uids = [uid.decode() for uid in unread_uids]
        if len(unread_uids) > 0:
            #fetch any unread
            response = await imap_client.uid('fetch', ','.join(unread_uids), 'RFC822')
            
            # start is: 2 FETCH (UID 18 RFC822 {42}
            # middle is the actual email content
            # end is simply ")"
            # the last line is removed as it's only "success"-ish information
            # the iter + zip tricks is to iterate three by three
            iterator = iter(response.lines[:-1])
            for start, middle, _end in zip(iterator, iterator, iterator):
                parsed_email = mailparser.parse_from_bytes(middle)
                print(parsed_email.to)
                print(parsed_email.subject)
                from_email = parsed_email.from_
                if len(parsed_email.reply_to) > 0:
                    from_email = parsed_email.reply_to
                print('from email::::')
                print(from_email)
                print(parsed_email.text_plain)
                print('message id::::')
                print(parsed_email.message_id)
                response = await processUnread(parsed_email.to, from_email, parsed_email.text_plain)
                if (response is not None) and len(response) > 0:
                    print(response)
                    await respondEmail(parsed_email.to, from_email, response, parsed_email)
        idle_task = await imap_client.idle_start(timeout=60)
        await imap_client.wait_server_push()
        imap_client.idle_done()
        await wait_for(idle_task, timeout=5)

def loop_and_retry():
    try:
        run(imap_loop(HOST, USER, PASSWORD))
    except Exception as e:
        print('Exception : ' + str(e))
        loop_and_retry()

if __name__ == '__main__':
    loop_and_retry()