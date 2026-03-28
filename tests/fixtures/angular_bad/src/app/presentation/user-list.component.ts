// BAD: Presentation imports Impl directly (violates rule 3)
import { UserServiceImpl } from '../domain/services/impl/user.service.impl';
// BAD: Presentation imports Data layer (violates rule 1, skips domain)
import { UserRepository } from '../data/repositories/user.repository';

export class UserListComponent {
  constructor(private userService: UserServiceImpl) {}
}
