pub trait UserRepository { fn find(&self, id: i64) -> Option<String>; }
