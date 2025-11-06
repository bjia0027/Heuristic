#pragma once
#include <functional>
#include <vector>

class Service3 {
public:
    Service3();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
