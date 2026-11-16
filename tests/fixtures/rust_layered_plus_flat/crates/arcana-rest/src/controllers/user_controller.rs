use axum::extract::{Path, State};
pub async fn get_user(State(app): State<App>, Path(id): Path<u64>) -> Json<User> {
    Json(app.users.get(id).await)
}
