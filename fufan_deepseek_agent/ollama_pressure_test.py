from openai import OpenAI

client = OpenAI(
    base_url='http://localhost:11434/v1/',
    api_key='ollama',
)
messages = [
    {
        'role': 'user',
        'content': '你好，请你介绍一下什么是人工智能？',
    }
]

try:
    # 调用聊天接口
    stream = client.chat.completions.create(
        model='deepseek-r1:14b',
        messages=messages,
        stream=True
    )
    
    # 处理流式响应
    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end='', flush=True)
            
except Exception as e:
    print(f"发生错误: {str(e)}")