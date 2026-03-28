package com.arcana.service.impl;

import com.arcana.service.UserService;
import com.arcana.repository.UserRepository;
import com.arcana.domain.User;

public class UserServiceImpl implements UserService {
    private final UserRepository userRepository;
    public UserServiceImpl(UserRepository repo) { this.userRepository = repo; }
    public User findById(Long id) { return userRepository.findById(id); }
}
