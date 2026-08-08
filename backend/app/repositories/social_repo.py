from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.post import Post
from app.models.comment import Comment
from app.models.reaction import Reaction
from app.models.follow import Follow


# ---- posts ----

def create_post(db: Session, citizen_id: int, content: str, commit: bool = True) -> Post:
    post = Post(citizen_id=citizen_id, content=content)
    db.add(post)
    if commit:
        db.commit()
        db.refresh(post)
    return post


def get_post(db: Session, post_id: int) -> Optional[Post]:
    return db.get(Post, post_id)


def list_posts_paginated(db: Session, offset: int, limit: int) -> tuple[list[Post], int]:
    total = db.scalar(select(func.count()).select_from(Post)) or 0
    posts = db.query(Post).order_by(Post.id.desc()).offset(offset).limit(limit).all()
    return posts, total


def count_comments(db: Session, post_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Comment).where(Comment.post_id == post_id)) or 0


def count_reactions(db: Session, post_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Reaction).where(Reaction.post_id == post_id)) or 0


# ---- comments ----

def create_comment(db: Session, post_id: int, citizen_id: int, content: str) -> Comment:
    comment = Comment(post_id=post_id, citizen_id=citizen_id, content=content)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def list_comments(db: Session, post_id: int) -> list[Comment]:
    return db.query(Comment).filter(Comment.post_id == post_id).order_by(Comment.id).all()


# ---- reactions ----

def get_reaction(db: Session, post_id: int, citizen_id: int) -> Optional[Reaction]:
    return (
        db.query(Reaction)
        .filter(Reaction.post_id == post_id, Reaction.citizen_id == citizen_id)
        .first()
    )


def create_reaction(db: Session, post_id: int, citizen_id: int, type_: str) -> Reaction:
    reaction = Reaction(post_id=post_id, citizen_id=citizen_id, type=type_)
    db.add(reaction)
    db.commit()
    db.refresh(reaction)
    return reaction


def delete_reaction(db: Session, reaction: Reaction) -> None:
    db.delete(reaction)
    db.commit()


# ---- follows ----

def get_follow(db: Session, follower_id: int, followee_id: int) -> Optional[Follow]:
    return (
        db.query(Follow)
        .filter(Follow.follower_id == follower_id, Follow.followee_id == followee_id)
        .first()
    )


def create_follow(db: Session, follower_id: int, followee_id: int) -> Follow:
    follow = Follow(follower_id=follower_id, followee_id=followee_id)
    db.add(follow)
    db.commit()
    db.refresh(follow)
    return follow


def delete_follow(db: Session, follow: Follow) -> None:
    db.delete(follow)
    db.commit()


def list_followers(db: Session, citizen_id: int) -> list[Follow]:
    return db.query(Follow).filter(Follow.followee_id == citizen_id).all()


def list_following(db: Session, citizen_id: int) -> list[Follow]:
    return db.query(Follow).filter(Follow.follower_id == citizen_id).all()
