import { User } from '../models/user.model';

export interface UserService {
  getUsers(): Promise<User[]>;
}
