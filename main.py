import http_client

def main():
    data = http_client.fetch("/last-updated.txt")
    print("Last update:", data.strip())

if __name__ == "__main__":
    main()