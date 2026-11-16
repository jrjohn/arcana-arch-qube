pub trait UserRepository { fn find(&self, id: u64) -> Option<User>; }
