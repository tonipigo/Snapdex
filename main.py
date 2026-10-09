# import http_client

# def main():
#     data = http_client.fetch("/last-updated.txt")
#     print("Last update:", data.strip())

# if __name__ == "__main__":
#     main()

# import json
# import os
# import http_client

# def main():
#     groups = http_client.fetch("/tcgplayer/85/groups", as_json=True)
#     print("Groups retrieved:", groups["totalItems"])

#     os.makedirs("exploration", exist_ok=True)

#     with open("exploration/groups_pokemon.json", "w", encoding="utf-8") as f:
#         json.dump(groups, f, indent=2)

#     print("Saved to exploration/groups_pokemon.json")

# if __name__ == "__main__":
#     main()

import json
import os
import http_client

def main():
    group_id = 23601  # ← sostituisci con il groupId che hai scelto

    products = http_client.fetch(f"/tcgplayer/85/{group_id}/products", as_json=True)
    print("Products retrieved:", products["totalItems"])

    prices = http_client.fetch(f"/tcgplayer/85/{group_id}/prices", as_json=True)
    print("Prices retrieved:", len(prices["results"]))

    os.makedirs("exploration", exist_ok=True)

    with open(f"exploration/products_{group_id}.json", "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2)

    with open(f"exploration/prices_{group_id}.json", "w", encoding="utf-8") as f:
        json.dump(prices, f, indent=2)

    print(f"Saved to exploration/products_{group_id}.json and exploration/prices_{group_id}.json")

if __name__ == "__main__":
    main()