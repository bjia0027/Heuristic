#pragma once
#include <functional>
#include <vector>

class Service17 {
public:
    Service17();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
