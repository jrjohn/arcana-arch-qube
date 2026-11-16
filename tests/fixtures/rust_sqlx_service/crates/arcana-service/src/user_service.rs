pub async fn delete_user(pool: &sqlx::MySqlPool, id: i64) -> anyhow::Result<()> {
    sqlx::query("DELETE FROM user WHERE id = ?").bind(id).execute(pool).await?;
    Ok(())
}
