#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv

load_dotenv()

import bcrypt
from memory.store import (
    create_user, get_user_by_email, get_user_by_id,
    create_session, get_all_memories
)
from agent.loop import AgentLoop

BANNER = """
=====================================
       AgentOS Phase 1
   Local Assistant with Memory
=====================================
"""

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def login_or_register():
    print("1) Login  2) Register")
    choice = input("Choice: ").strip()

    if choice == "2":
        email = input("Email: ").strip()
        password = input("Password: ").strip()
        name = input("Name (optional): ").strip() or None
        user = get_user_by_email(email)
        if user:
            print("Email already registered. Try login.")
            return login_or_register()
        user = create_user(email, hash_password(password), name)
        print(f"Registered as {email}")
        return user
    else:
        email = input("Email: ").strip()
        password = input("Password: ").strip()
        user = get_user_by_email(email)
        if not user or not check_password(password, user["password_hash"]):
            print("Invalid credentials.")
            return login_or_register()
        print(f"Welcome back, {user.get('name') or email}!")
        return user

def main():
    print(BANNER)

    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY not set.")
        print("Create a .env file with: GEMINI_API_KEY=your-key")
        sys.exit(1)

    user = login_or_register()
    session = create_session(user["id"])
    agent = AgentLoop()

    print(f"\nSession started: {session['id'][:8]}...")
    print("Commands:")
    print("  /memories  - Show saved memories")
    print("  /session   - Start new session")
    print("  /exit      - Exit")
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            print("Goodbye!")
            break
        elif user_input == "/help":
            print("Commands: /memories, /session, /exit")
            continue
        elif user_input == "/memories":
            memories = get_all_memories(user["id"])
            if memories:
                for m in memories:
                    print(f"  [{m['importance']}] {m['key']}: {m['content'][:100]}")
            else:
                print("  No memories stored yet.")
            continue
        elif user_input == "/session":
            session = create_session(user["id"])
            print(f"New session: {session['id'][:8]}...")
            continue

        print(f"\nAgent: ", end="", flush=True)
        try:
            response = agent.run(session["id"], user["id"], user_input)
            print(response)
        except Exception as e:
            print(f"\nError: {e}")
        print()

if __name__ == "__main__":
    main()
