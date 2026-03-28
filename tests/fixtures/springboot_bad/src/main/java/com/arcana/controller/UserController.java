package com.arcana.controller;

// BAD: Controller imports DAO directly (violates rule 18)
import com.arcana.dao.impl.UserDaoImpl;
// BAD: Controller imports ServiceImpl (violates rule 3)
import com.arcana.service.impl.UserServiceImpl;

public class UserController {
    private final UserDaoImpl userDao;
    public UserController(UserDaoImpl dao) {
        this.userDao = dao;
    }
}
