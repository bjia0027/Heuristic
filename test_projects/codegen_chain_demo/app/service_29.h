#pragma once
#include <functional>
#include <vector>

class Service29 {
public:
    Service29();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
