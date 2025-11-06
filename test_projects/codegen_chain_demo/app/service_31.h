#pragma once
#include <functional>
#include <vector>

class Service31 {
public:
    Service31();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
