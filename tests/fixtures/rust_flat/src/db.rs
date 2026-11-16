pub async fn load(pool: &sqlx::MySqlPool) -> anyhow::Result<()> {
    let _rows = sqlx::query("SELECT id, name FROM user WHERE id = ?").bind(1).fetch_all(pool).await?;
    Ok(())
}
