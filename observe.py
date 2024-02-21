ALL_EMAILS = [
    "captain@fraind.email"
]

class Observer:
    def __init__(self):
        self.emails = ALL_EMAILS

        self.imap_client = aioimaplib.IMAP4_SSL(host=host, timeout=30)
        await imap_client.wait_hello_from_server()

        await imap_client.login(user, password)
        await imap_client.select('INBOX')

    def get_updates(self):
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
                print(parsed_email.message_id)
                print(parsed_email.subject)
                print(parsed_email.from_)
                print(parsed_email.text_plain)
                response = await processUnread(parsed_email.from_, parsed_email.text_plain)
                if len(response) > 0:
                    print(response)
                    await respondEmail(response, parsed_email)
        idle_task = await imap_client.idle_start(timeout=60)
        await imap_client.wait_server_push()
        imap_client.idle_done()
        await wait_for(idle_task, timeout=5)
        

    