import { UserService } from '../user.service';
import { UserRepository } from '../../data/repositories/user.repository';

export class UserServiceImpl implements UserService {
  constructor(private repo: UserRepository) {}
  async getUsers() { return this.repo.findAll(); }
}
