#pragma once
#include <functional>
#include <vector>

class Service21 {
public:
    Service21();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
