use axum::extract::{Query, State};
use std::path::Path;
// 一般函式用 std::path::Path,不是 handler —— 不能被判成違規。
pub fn helper(p: &Path) -> bool { p.exists() }
async fn search_page(
    State(state): State<AppState>,
    Query(q): Query<SearchQuery>,
) -> Response {
    let hits = state.index.search(&q.text).await;
    render(hits)
}
pub async fn recent_moves_json(State(state): State<AppState>) -> Response {
    todo!()
}
