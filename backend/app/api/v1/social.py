from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.social import (
    PostCreate,
    PostOut,
    FeedResponse,
    CommentCreate,
    CommentOut,
    ReactionCreate,
    ReactionOut,
    FollowOut,
)
from app.services import social_service
from app.services.social_service import (
    SocialError,
    PostNotFound,
    ReactionAlreadyExists,
    ReactionNotFound,
    CannotFollowSelf,
    FollowAlreadyExists,
    FollowNotFound,
)

router = APIRouter(prefix="/api/v1", tags=["social"])


@router.post("/citizens/{citizen_id}/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED)
def create_post(
    citizen_id: int,
    payload: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually create a post as a given citizen. The primary path for posts
    is the tick engine's `create_post` action — this endpoint exists for
    testing/seeding, same pattern as citizen create/update."""
    try:
        return social_service.create_post(db, citizen_id, payload.content)
    except SocialError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/feed", response_model=FeedResponse)
def get_feed(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public — most recent posts first, with citizen name + comment/reaction counts."""
    items, total = social_service.get_feed(db, page=page, page_size=page_size)
    return {"total": total, "items": items}


@router.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(
    post_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return social_service.add_comment(
            db, post_id, payload.citizen_id, payload.content, parent_comment_id=payload.parent_comment_id
        )
    except PostNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except SocialError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)


@router.get("/posts/{post_id}/comments", response_model=list[CommentOut])
def list_comments(post_id: int, db: Session = Depends(get_db)):
    try:
        return social_service.list_comments(db, post_id)
    except PostNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.post("/posts/{post_id}/reactions", response_model=ReactionOut, status_code=status.HTTP_201_CREATED)
def add_reaction(
    post_id: int,
    payload: ReactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return social_service.add_reaction(db, post_id, payload.citizen_id, payload.type)
    except PostNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ReactionAlreadyExists as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except SocialError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)


@router.delete("/posts/{post_id}/reactions/{citizen_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_reaction(
    post_id: int,
    citizen_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        social_service.remove_reaction(db, post_id, citizen_id)
    except ReactionNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.post(
    "/citizens/{citizen_id}/follow/{target_id}",
    response_model=FollowOut,
    status_code=status.HTTP_201_CREATED,
)
def follow_citizen(
    citizen_id: int,
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return social_service.follow(db, citizen_id, target_id)
    except CannotFollowSelf as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except FollowAlreadyExists as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except SocialError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.delete("/citizens/{citizen_id}/follow/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_citizen(
    citizen_id: int,
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        social_service.unfollow(db, citizen_id, target_id)
    except FollowNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/citizens/{citizen_id}/followers", response_model=list[FollowOut])
def get_followers(citizen_id: int, db: Session = Depends(get_db)):
    return social_service.list_followers(db, citizen_id)


@router.get("/citizens/{citizen_id}/following", response_model=list[FollowOut])
def get_following(citizen_id: int, db: Session = Depends(get_db)):
    return social_service.list_following(db, citizen_id)
