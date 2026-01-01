#!/usr/bin/env python3
"""
LINEPY Timeline / Square Note Test
"""

import sys

sys.path.insert(0, ".")

from linepy.base import BaseClient
from linepy.thrift import set_debug

# set_debug(True)
set_debug(False)


def test_timeline():
    print("=" * 50)
    print("  Timeline / Square Note Test")
    print("=" * 50)

    client = BaseClient(device="IOSIPAD", storage=".linepy_test.json")

    if not client.auto_login():
        print("❌ Need login")
        client.login_with_qr()

    print(f"Logged in as: {client.profile.get(20)}")

    # 1. Get joined squares (using new Pydantic models)
    try:
        squares_resp = client.square.get_joined_squares(limit=10)
        squares = squares_resp.squares
        print(f"Joined squares count: {len(squares)}")
        if squares:
            first_square = squares[0]
            print(f"First Square: {first_square.name} ({first_square.mid})")

            # Use this found square if we want dynamic target
            # square_mid = first_square.mid
    except Exception as e:
        print(f"❌ Failed to get joined squares: {e}")

    # Use a specific square that we know works
    # s4a7476f1b4fbe40be48b663bbe59c622 - 実験の名前変更
    square_mid = "s4a7476f1b4fbe40be48b663bbe59c622"
    print(f"\nTarget Square MID: {square_mid}")

    # 2. List existing notes (posts)
    print("\n--- Listing Posts ---")
    try:
        posts = client.timeline.list_post(home_id=square_mid)
        # Using Pydantic models with dot access
        print(f"Response code: {posts.code}, message: {posts.message}")
        print(f"Number of feeds: {len(posts.result.feeds)}")
        if posts.result.feeds:
            first_post = posts.result.feeds[0].post
            print(f"First post text: {first_post.contents.text}")
            print(f"First post ID: {first_post.postInfo.postId}")
        print("✅ List success")
    except Exception as e:
        print(f"❌ List failed: {e}")
        import traceback

        traceback.print_exc()

    # 3. Create a note
    print("\n--- Creating Note ---")
    try:
        post = client.timeline.create_post(
            home_id=square_mid, text="Hello world from LINEPY!\n(Test post)"
        )
        # Using Pydantic models with dot access
        print(f"Create response code: {post.code}, message: {post.message}")
        # Access via Pydantic model
        created_post = post.result.feed.post
        post_id = created_post.postInfo.postId
        print(f"Post ID: {post_id}")
        print(f"Post text: {created_post.contents.text}")
        print("✅ Create success")

        # 4. Delete the note
        print(f"\n--- Deleting Note ({post_id}) ---")
        delete_resp = client.timeline.delete_post(home_id=square_mid, post_id=post_id)
        print(
            f"Delete response code: {delete_resp.code}, message: {delete_resp.message}"
        )
        print("✅ Delete success")

    except Exception as e:
        print(f"❌ Create/Delete failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_timeline()
