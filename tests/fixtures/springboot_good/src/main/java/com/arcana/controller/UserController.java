package com.arcana.controller;

import com.arcana.service.UserService;
import com.arcana.domain.dto.UserDto;

public class UserController {
    private final UserService userService;
    public UserController(UserService userService) {
        this.userService = userService;
    }
}
