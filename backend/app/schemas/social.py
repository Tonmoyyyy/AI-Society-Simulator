from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    citizen_id: int
    content: str
    created_at: datetime


class PostWithMeta(BaseModel):
    id: int
    citizen_id: int
    citizen_name: str
    content: str
    created_at: datetime
    comment_count: int
    reaction_count: int


class FeedResponse(BaseModel):
    total: int
    items: list[PostWithMeta]


class CommentCreate(BaseModel):
    citizen_id: int
    content: str = Field(min_length=1, max_length=1000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    citizen_id: int
    content: str
    created_at: datetime


class ReactionCreate(BaseModel):
    citizen_id: int
    type: str = Field(default="like", max_length=20)


class ReactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    citizen_id: int
    type: str
    created_at: datetime


class FollowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    follower_id: int
    followee_id: int
    created_at: datetime
