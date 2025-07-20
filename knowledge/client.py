from knowledge.api import ask

def main():
    print("欢迎使用知识库问答测试客户端。输入 'exit' 退出。")
    while True:
        question = input("请输入你的问题：")
        if question.strip().lower() == 'exit':
            break
        answer = ask(question)
        print(f"答复：{answer}\n")

if __name__ == "__main__":
    main() 