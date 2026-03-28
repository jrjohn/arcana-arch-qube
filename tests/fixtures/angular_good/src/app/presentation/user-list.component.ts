import { UserService } from '../domain/services/user.service';
import { User } from '../domain/models/user.model';

export class UserListComponent {
  constructor(private userService: UserService) {}
}
