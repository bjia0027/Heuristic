#pragma once
#include <functional>
#include <vector>

class Service20 {
public:
    Service20();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
