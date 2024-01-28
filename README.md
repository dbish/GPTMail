This is very rough code with a simple "respond with this prompt" example, looking for feedback though if anyone else would want to use it for GPTs or other use cases. It works well enough for my basic use case right now and I run it with some other code that I use to reason over my inbox. Simple steps:
1. Use IMAP with IDLE to wait for new messages
2. Determine if you want to respond and send the reply + thread as history to GPT
3. Use SMTP to send a response

This all runs on EC2 for me right now, and security is handled using a gmail app password, but there are a variety of ways to make this work for more people. Feel free to ping me if you're just trying to run it yourself.
