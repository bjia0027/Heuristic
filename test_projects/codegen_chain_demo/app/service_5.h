#pragma once
#include <functional>
#include <vector>

class Service5 {
public:
    Service5();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
