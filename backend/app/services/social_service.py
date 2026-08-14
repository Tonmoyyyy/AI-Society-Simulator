from sqlalchemy.orm import Session

from app.repositories import citizen_repo, social_repo
from app.websocket.connection_manager import manager


class SocialError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class PostNotFound(SocialError):
    pass


class ReactionAlreadyExists(SocialError):
    pass


class ReactionNotFound(SocialError):
    pass


class CannotFollowSelf(SocialError):
    pass


class FollowAlreadyExists(SocialError):
    pass


class FollowNotFound(SocialError):
    pass


def _require_citizen(db: Session, citizen_id: int):
    citizen = citizen_repo.get_by_id(db, citizen_id)
    if citizen is None:
        raise SocialError(f"Citizen {citizen_id} not found")
    return citizen


def create_post(db: Session, citizen_id: int, content: str):
    citizen = _require_citizen(db, citizen_id)
    post = social_repo.create_post(db, citizen_id, content)
    manager.broadcast_threadsafe({
        "type": "new_post",
        "post_id": post.id,
        "citizen_id": citizen_id,
        "citizen_name": citizen.name,
        "content": post.content,
    })
    return post


def get_feed(db: Session, page: int, page_size: int) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    posts, total = social_repo.list_posts_paginated(db, offset=offset, limit=page_size)
    items = []
    for post in posts:
        citizen = citizen_repo.get_by_id(db, post.citizen_id)
        items.append({
            "id": post.id,
            "citizen_id": post.citizen_id,
            "citizen_name": citizen.name if citizen else "Unknown",
            "content": post.content,
            "created_at": post.created_at,
            "comment_count": social_repo.count_comments(db, post.id),
            "reaction_count": social_repo.count_reactions(db, post.id),
        })
    return items, total


def add_comment(db: Session, post_id: int, citizen_id: int, content: str, parent_comment_id: int | None = None):
    post = social_repo.get_post(db, post_id)
    if post is None:
        raise PostNotFound(f"Post {post_id} not found")
    citizen = _require_citizen(db, citizen_id)

    if parent_comment_id is not None:
        parent = social_repo.get_comment(db, parent_comment_id)
        if parent is None or parent.post_id != post_id:
            raise SocialError(f"Parent comment {parent_comment_id} not found on this post")

    comment = social_repo.create_comment(db, post_id, citizen_id, content, parent_comment_id=parent_comment_id)
    manager.broadcast_threadsafe({
        "type": "new_comment",
        "post_id": post_id,
        "citizen_id": citizen_id,
        "citizen_name": citizen.name,
        "content": comment.content,
        "parent_comment_id": parent_comment_id,
    })
    return comment


def list_comments(db: Session, post_id: int):
    post = social_repo.get_post(db, post_id)
    if post is None:
        raise PostNotFound(f"Post {post_id} not found")
    return social_repo.list_comments(db, post_id)


def add_reaction(db: Session, post_id: int, citizen_id: int, type_: str):
    post = social_repo.get_post(db, post_id)
    if post is None:
        raise PostNotFound(f"Post {post_id} not found")
    _require_citizen(db, citizen_id)

    if social_repo.get_reaction(db, post_id, citizen_id) is not None:
        raise ReactionAlreadyExists("This citizen already reacted to this post")
    return social_repo.create_reaction(db, post_id, citizen_id, type_)


def remove_reaction(db: Session, post_id: int, citizen_id: int):
    existing = social_repo.get_reaction(db, post_id, citizen_id)
    if existing is None:
        raise ReactionNotFound("No reaction found to remove")
    social_repo.delete_reaction(db, existing)


def follow(db: Session, follower_id: int, followee_id: int):
    if follower_id == followee_id:
        raise CannotFollowSelf("A citizen cannot follow themselves")
    _require_citizen(db, follower_id)
    _require_citizen(db, followee_id)

    if social_repo.get_follow(db, follower_id, followee_id) is not None:
        raise FollowAlreadyExists("Already following")
    return social_repo.create_follow(db, follower_id, followee_id)


def unfollow(db: Session, follower_id: int, followee_id: int):
    existing = social_repo.get_follow(db, follower_id, followee_id)
    if existing is None:
        raise FollowNotFound("Not following")
    social_repo.delete_follow(db, existing)


def list_followers(db: Session, citizen_id: int):
    return social_repo.list_followers(db, citizen_id)


def list_following(db: Session, citizen_id: int):
    return social_repo.list_following(db, citizen_id)
