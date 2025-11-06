#pragma once
#include <functional>
#include <vector>

class Service39 {
public:
    Service39();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
