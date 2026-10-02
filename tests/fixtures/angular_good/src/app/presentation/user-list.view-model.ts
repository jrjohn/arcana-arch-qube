import { UserService } from '../domain/services/user.service';
import { User } from '../domain/models/user.model';

export class UserListViewModel {
  users: User[] = [];
  constructor(private userService: UserService) {}
  async load(): Promise<void> { this.users = await this.userService.getUsers(); }
}
