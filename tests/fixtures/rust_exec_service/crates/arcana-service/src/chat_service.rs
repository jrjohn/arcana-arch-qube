pub struct ToolExec;
impl ToolExec { pub async fn execute(&self, name: &str) -> (String, bool) { (name.into(), false) } }
pub async fn answer(exec: &ToolExec) -> String {
    let (out, is_error) = exec.execute("dealer_find_customer").await;
    if is_error { String::new() } else { out }
}
