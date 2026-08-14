"""
Makes "socialize" mean something between citizens, not just a private mood
boost. When a citizen's chosen tick action is socialize, this picks a
random other citizen and maybe reacts to / comments on their most recent
post, and maybe follows them.

Deliberately kept as a secondary effect layered on top of the existing
utility-scored FSM (see decision_pipeline.py) rather than adding
comment/react/follow as competing primary actions: those would need to
score "who to target," which the current utility functions (personality +
own state only) aren't built for, and this reuses the existing "socialize"
utility exactly as-is. If a future phase wants targeted social actions to
compete on their own utility, this is the natural place to expand from.
"""

import random

from app.repositories import social_repo
from app.simulation.comment_content import generate_comment_content

REACT_PROBABILITY = 0.5
COMMENT_PROBABILITY = 0.3
FOLLOW_PROBABILITY = 0.15


def perform_social_interaction(db, citizen, other_citizens, broadcast_queue) -> None:
    """All writes are batched (commit=False) into the caller's tick
    transaction — same pattern as posts and salary. Appends any realtime
    events to broadcast_queue for the caller to send after the commit."""
    candidates = [c for c in other_citizens if c.id != citizen.id]
    if not candidates:
        return
    target = random.choice(candidates)

    post = social_repo.get_most_recent_post(db, target.id)
    if post is not None:
        if random.random() < REACT_PROBABILITY and social_repo.get_reaction(db, post.id, citizen.id) is None:
            social_repo.create_reaction(db, post.id, citizen.id, "like", commit=False)
            broadcast_queue.append({
                "type": "new_reaction",
                "post_id": post.id,
                "citizen_id": citizen.id,
                "citizen_name": citizen.name,
                "target_citizen_name": target.name,
            })

        if random.random() < COMMENT_PROBABILITY:
            # If others have already commented on this post, sometimes
            # reply to one of their comments directly — a real threaded
            # reply (parent_comment_id set), not just a top-level comment
            # that happens to mention them. Combined with the @name
            # addressing in comment_content.py, this is what turns
            # isolated one-off comments into an actual back-and-forth
            # between citizens.
            existing_comments = social_repo.list_comments(db, post.id)
            other_comments = [c for c in existing_comments if c.citizen_id != citizen.id]
            parent_comment = random.choice(other_comments) if other_comments else None

            reply_to_name = None
            if parent_comment is not None:
                match = next((c for c in other_citizens if c.id == parent_comment.citizen_id), None)
                if match is not None:
                    reply_to_name = match.name

            content = generate_comment_content(citizen.personality_json, reply_to_name=reply_to_name)
            social_repo.create_comment(
                db, post.id, citizen.id, content,
                parent_comment_id=parent_comment.id if parent_comment else None,
                commit=False,
            )
            broadcast_queue.append({
                "type": "new_comment",
                "post_id": post.id,
                "citizen_id": citizen.id,
                "citizen_name": citizen.name,
                "content": content,
                "parent_comment_id": parent_comment.id if parent_comment else None,
            })

    if random.random() < FOLLOW_PROBABILITY and social_repo.get_follow(db, citizen.id, target.id) is None:
        social_repo.create_follow(db, citizen.id, target.id, commit=False)
        broadcast_queue.append({
            "type": "new_follow",
            "citizen_id": citizen.id,
            "citizen_name": citizen.name,
            "target_citizen_id": target.id,
            "target_citizen_name": target.name,
        })
